from django.contrib import admin
from .models import ExhibitorProfile, Exhibition, VisitorRegistration
# Register your models here.

admin.site.register(ExhibitorProfile)
admin.site.register(Exhibition)
admin.site.register(VisitorRegistration)