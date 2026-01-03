from django.contrib import admin
from .models import ExhibitorProfile, Exhibition, VisitorRegistration, ExhibitorApplication, Property, PropertyImage, ExhibitionImage
# Register your models here.

admin.site.register(ExhibitorProfile)
admin.site.register(Exhibition)
admin.site.register(VisitorRegistration)
admin.site.register(ExhibitorApplication)
admin.site.register(Property)
admin.site.register(PropertyImage)
admin.site.register(ExhibitionImage)