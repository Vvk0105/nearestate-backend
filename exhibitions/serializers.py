from rest_framework import serializers
from .models import Exhibition, ExhibitionImage, Property, PropertyImage


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
