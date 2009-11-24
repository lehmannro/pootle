#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 
# Copyright 2008 Zuza Software Foundation
# 
# This file is part of translate.
#
# translate is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# 
# translate is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with translate; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

from django.db import models
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals           import pre_delete, post_save

from pootle_app.lib.util import RelatedManager
from pootle_app.models.directory import Directory

def get_pootle_permission(codename):
    # The content type of our permission
    content_type = ContentType.objects.get(name='pootle', app_label='pootle_app')
    # Get the pootle view permission
    return Permission.objects.get(content_type=content_type, codename=codename)

def get_pootle_permissions(codenames=None):
    """gets the available rights and their localized names"""
    # l10n: Verb
    content_type = ContentType.objects.get(name='pootle', app_label='pootle_app')
    if codenames is not None:
        permissions = Permission.objects.filter(content_type=content_type, codename__in=codenames)
    else:
        permissions = Permission.objects.filter(content_type=content_type)
    return dict((permission.codename, permission) for permission in permissions)

def get_permission_set_by_username(username, directory):
    try:
        return PermissionSet.objects.get(profile__user__username=username, directory=directory)
    except PermissionSet.DoesNotExist:
        pass
    try:
        return PermissionSet.objects.get(profile__user__username='default', directory=directory)
    except PermissionSet.DoesNotExist:
        return None

def get_matching_permission_set(profile, directory):
    if profile.user.is_authenticated():
        try:
            return PermissionSet.objects.get(profile=profile, directory=directory)
        except PermissionSet.DoesNotExist:
            return get_permission_set_by_username('default', directory)
    else:
        return get_permission_set_by_username('nobody', directory)

def get_matching_permissions_recurse(profile, directory):
    """Build a (permission codename -> permission) dictionary which
    reflects the permissions that the PootleProfile 'profile' has in
    the directory 'directory'. This is done by taking the permissions
    associated with 'profile' in all parent directories into account.

    Recurse from 'directory' all the way up to the root directory.
    Once we hit the root, find a PermissionSet which matches the
    supplied PootleProfile 'profile' and Directory 'directory'. Add
    the positive permissions from this PermissionSet to the dictionary
    which we are building and use the negative permissions associated
    with the root directory to remove permissions from the permissions
    dictionary.
    
    Once this has been done for the root directory, we recurse one
    level up and do the same to the child directory and so on until we
    reach the directory from which we started this process. By that
    point we'll have a permissions dictionary reflecting the
    permissions that 'profile' has in 'directory'."""
    if directory.parent is not None:
        permissions = get_matching_permissions(profile, directory.parent)
    else:
        permissions = {}

    permission_set = get_matching_permission_set(profile, directory)
    if permission_set is not None:
        permissions.update((permission.codename, permission)
                           for permission in permission_set.positive_permissions.all())
        for permission in permission_set.negative_permissions.all():
            if permission.codename in permissions:
                del permissions[permission.codename]
    return permissions

def get_matching_permissions(profile, directory):
    try:
        cached_permission_set = PermissionSetCache.objects.get(profile=profile, directory=directory)
        return dict((permission.codename, permission) for permission in cached_permission_set.permissions.all())
    except PermissionSetCache.DoesNotExist:
        permissions = get_matching_permissions_recurse(profile, directory)
        # Ensure that administrative superusers always get admin rights
        if profile.user.is_superuser and 'administrate' not in permissions:
            permissions['administrate'] = get_pootle_permission('administrate')
        cached_permission_set = PermissionSetCache(profile=profile, directory=directory)
        cached_permission_set.save()
        cached_permission_set.permissions = permissions.values()
        cached_permission_set.save()
        return permissions


def check_profile_permission(profile, permission_codename, directory):
    """it checks if current user has the permission the perform C{permission_codename}"""
    if profile.user.is_superuser:
        return True
    permissions = get_matching_permissions(profile, directory)
    return permission_codename in permissions

def check_permission(permission_codename, request):
    """it checks if current user has the permission the perform C{permission_codename}"""
    if request.user.is_superuser:
        return True
    return permission_codename in request.permissions

class PermissionSet(models.Model):
    objects = RelatedManager()
    class Meta:
        unique_together = ('profile', 'directory')
        app_label = "pootle_app"

    profile                = models.ForeignKey('pootle_app.PootleProfile', db_index=True)
    directory              = models.ForeignKey(Directory, db_index=True, related_name='permission_sets')
    positive_permissions   = models.ManyToManyField(Permission, db_index=True, related_name='permission_sets_positive')
    negative_permissions   = models.ManyToManyField(Permission, db_index=True, related_name='permission_sets_negative')

class PermissionSetCache(models.Model):
    objects = RelatedManager()
    class Meta:
        unique_together = ('profile', 'directory')
        app_label = "pootle_app"
        

    profile                = models.ForeignKey('pootle_app.PootleProfile', db_index=True)
    directory              = models.ForeignKey(Directory, db_index=True, related_name='permission_set_caches')
    permissions            = models.ManyToManyField(Permission, related_name='cached_permissions', db_index=True)

class PermissionError(Exception):
    pass

def nuke_permission_set_caches(profile, directory):
    """Delete all PermissionSetCache objects matching the current
    profile and whose directories are subdirectories of directory."""
    for permission_set_cache in PermissionSetCache.objects.filter(profile=profile, directory__pootle_path__startswith=directory.pootle_path):
        permission_set_cache.delete()

def void_cached_permissions(sender, instance, **kwargs):
    if instance.profile.user.username == 'default':
        profile_to_permission_set = dict((permission_set.profile, permission_set) for permission_set
                                            in PermissionSet.objects.filter(directory=instance.directory))
        for permission_set_cache in PermissionSetCache.objects.filter(directory=instance.directory):
            if permission_set_cache.profile not in profile_to_permission_set:
                nuke_permission_set_caches(permission_set_cache.profile, instance.directory)
    else:
        nuke_permission_set_caches(instance.profile, instance.directory)

post_save.connect(void_cached_permissions, sender=PermissionSet)
pre_delete.connect(void_cached_permissions, sender=PermissionSet)
