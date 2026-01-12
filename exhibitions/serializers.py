from rest_framework import serializers
from .models import Exhibition, ExhibitionImage, Property, PropertyImage, ExhibitorProfile
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxLengthValidator
import re

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
    
    def validate_company_name(self, value):
        if len(value) > 200:
            raise serializers.ValidationError("Company name cannot exceed 200 characters")
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Company name must be at least 2 characters")
        return value.strip()
    
    def validate_contact_number(self, value):
        # Remove spaces and dashes for validation
        cleaned = re.sub(r'[\s\-\(\)]', '', value)
        if not re.match(r'^\+?\d{8,15}$', cleaned):
            raise serializers.ValidationError("Please enter a valid phone number (8-15 digits)")
        return value
    
    def validate_council_area(self, value):
        if len(value) > 100:
            raise serializers.ValidationError("Council area cannot exceed 100 characters")
        return value.strip()
    
class ExhibitionImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExhibitionImage
        fields = ["id", "image"]


class ExhibitionSerializer(serializers.ModelSerializer):
    images = ExhibitionImageSerializer(many=True, read_only=True)

    class Meta:
        model = Exhibition
        fields = "__all__"
    
    def validate_name(self, value):
        if len(value) > 200:
            raise serializers.ValidationError("Event name cannot exceed 200 characters")
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Event name must be at least 3 characters")
        return value.strip()
    
    def validate_description(self, value):
        if len(value) > 1000:
            raise serializers.ValidationError("Description cannot exceed 1000 characters")
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Description must be at least 10 characters")
        return value.strip()
    
    def validate_booth_capacity(self, value):
        if value < 1:
            raise serializers.ValidationError("Booth capacity must be at least 1")
        if value > 10000:
            raise serializers.ValidationError("Booth capacity cannot exceed 10000")
        return value
    
    def validate_visitor_capacity(self, value):
        if value < 1:
            raise serializers.ValidationError("Visitor capacity must be at least 1")
        if value > 100000:
            raise serializers.ValidationError("Visitor capacity cannot exceed 100000")
        return value
    
    def validate(self, data):
        # Validate end date is after start date
        if 'start_date' in data and 'end_date' in data:
            if data['end_date'] < data['start_date']:
                raise serializers.ValidationError({
                    "end_date": "End date must be after start date"
                })
        return data

class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ["id", "image"]


class PropertySerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = "__all__"
    
    def validate_title(self, value):
        if len(value) > 200:
            raise serializers.ValidationError("Title cannot exceed 200 characters")
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Title must be at least 3 characters")
        return value.strip()
    
    def validate_description(self, value):
        if len(value) > 2000:
            raise serializers.ValidationError("Description cannot exceed 2000 characters")
        return value.strip()
    
    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price cannot be negative")
        if value > 999999999:
            raise serializers.ValidationError("Price is too large")
        return value

