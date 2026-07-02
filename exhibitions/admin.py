from django.contrib import admin
from .models import (
    ExhibitorProfile, Exhibition, VisitorRegistration, ExhibitorApplication,
    Property, PropertyImage, ExhibitionImage,
    EventRecap, RecapImage, RecapVideo, RecapSocialLink,
    ExhibitionPriceTier,
)

admin.site.register(ExhibitorProfile)
admin.site.register(Exhibition)
admin.site.register(VisitorRegistration)
admin.site.register(ExhibitorApplication)
admin.site.register(Property)
admin.site.register(PropertyImage)
admin.site.register(ExhibitionImage)
admin.site.register(EventRecap)
admin.site.register(RecapImage)
admin.site.register(RecapVideo)
admin.site.register(RecapSocialLink)
admin.site.register(ExhibitionPriceTier)