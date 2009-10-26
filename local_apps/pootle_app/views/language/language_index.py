#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2004-2009 Zuza Software Foundation
#
# This file is part of translate.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

from django.shortcuts import get_object_or_404
from django.utils.translation import ugettext as _
from django.utils.translation import ungettext
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.core.exceptions import PermissionDenied

from pootle_app.views.language.project_index import get_stats_headings
from pootle_app.views.language.item_dict import add_percentages
from pootle_app.views import pagelayout
from pootle_app.views.indexpage import shortdescription, gentopstats
from pootle_app.models import Suggestion, Submission, Language

from pootle.i18n.gettext import tr_lang

from pootle_app.models.permissions import get_matching_permissions, check_permission
from pootle_app.models.profile import get_profile

def limit(query):
    return query[:5]

def make_project_item(translation_project):
    project = translation_project.project
    href = '%s/' % project.code
    projectstats = add_percentages(translation_project.getquickstats())
    return {
        'code': project.code,
        'href': href,
        'icon': 'folder',
        'title': project.fullname,
        'description': project.description,
        'data': projectstats,
        'isproject': True,
        }

def language_index(request, language_code):
    language = get_object_or_404(Language, code=language_code)
    request.permissions = get_matching_permissions(get_profile(request.user), language.directory)

    if not check_permission("view", request):
        raise PermissionDenied

    projects = language.translationproject_set.all()
    projectcount = len(projects)
    items = (make_project_item(translate_project) for translate_project in projects)

    totals = language.getquickstats()
    average = totals['translatedsourcewords'] * 100 / max(totals['totalsourcewords'], 1)

    def narrow(query):
        return limit(query.filter(translation_project__language__code=language_code))

    topsugg = narrow(Suggestion.objects.get_top_suggesters())
    topreview = narrow(Suggestion.objects.get_top_reviewers())
    topsub = narrow(Submission.objects.get_top_submitters())
    topstats = gentopstats(topsugg, topreview, topsub)

    templatevars = {
        'pagetitle': _('%(title)s: Language %(language)s',
                       {"title": pagelayout.get_title(), "language": tr_lang(language.fullname)}),
        'language': {
          'code': language.code,
          'name': tr_lang(language.fullname),
          'stats': ungettext('%(projects)d project, %(average)d%% translated',
                             '%(projects)d projects, %(average)d%% translated',
                             projectcount, {"projects": projectcount, "average": average}),
        },
        'projects': items,
        'statsheadings': get_stats_headings(),
        'topstats': topstats,
        'instancetitle': pagelayout.get_title(),
        }
    return render_to_response("language/language_index.html", templatevars, context_instance=RequestContext(request))
