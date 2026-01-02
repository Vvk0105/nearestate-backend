from rest_framework import serializers
from .models import Exhibition, ExhibitionImage


class ExhibitionImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExhibitionImage
        fields = ["id", "image"]


class ExhibitionSerializer(serializers.ModelSerializer):
    images = ExhibitionImageSerializer(many=True, read_only=True)

    class Meta:
        model = Exhibition
        fields = "__all__"
