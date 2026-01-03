from rest_framework import serializers
from .models import Exhibition, ExhibitionImage, Property, PropertyImage, ExhibitorProfile
from django.contrib.auth import get_user_model

User = get_user_model()


class ExhibitorUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "active_role",
        ]

class ExhibitorProfileSerializer(serializers.ModelSerializer):
    user = ExhibitorUserSerializer(read_only=True)

    class Meta:
        model = ExhibitorProfile
        fields = [
            "id",
            "user",
            "company_name",
            "council_area",
            "business_type",
            "contact_number",
        ]
    
class ExhibitionImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExhibitionImage
        fields = ["id", "image"]


class ExhibitionSerializer(serializers.ModelSerializer):
    images = ExhibitionImageSerializer(many=True, read_only=True)

    class Meta:
        model = Exhibition
        fields = "__all__"

class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ["id", "image"]


class PropertySerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = "__all__"
