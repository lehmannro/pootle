from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponseRedirect

from jToolkit import prefs

from Pootle import pan_app, adminpages
from Pootle.views.util import render_jtoolkit
from Pootle.views.main import _pootle

def user_is_admin(f):
    def decorated_f(request, *args, **kwargs):
        if not request.user.is_authenticated:
            request.message = request.localize("You must log in to administer Pootle.")
            return HttpResponseRedirect('/login') # TODO: Hardcoding is awful. Fix this.
        elif not request.user.is_superuser:
            request.message = request.localize("You do not have the rights to administer Pootle.")
            return HttpResponseRedirect('/home') # TODO: Hardcoding is awful. Fix this.
        else:
            return f(request, *args, **kwargs)
    return decorated_f

@user_is_admin
def index(request, path):
    if request.method == 'POST':
        prefs.change_preferences(pan_app.prefs, arg_dict)
    return render_jtoolkit(adminpages.AdminPage(request))

@user_is_admin
def users(request):
    if request.method == 'POST':
        _pootle.changeusers(request, request.POST.copy())
    return render_jtoolkit(adminpages.UsersAdminPage(_pootle, request))

@user_is_admin
def languages(request):
    if request.method == 'POST':
        pan_app.get_po_tree().changelanguages(request.POST.copy())
    return render_jtoolkit(adminpages.LanguagesAdminPage(request))

@user_is_admin
def projects(request):
    if request.method == 'POST':
        pan_app.get_po_potree().changeprojects(request.POST.copy())
    return render_jtoolkit(adminpages.ProjectsAdminPage(request))