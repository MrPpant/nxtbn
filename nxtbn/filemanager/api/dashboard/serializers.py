from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from nxtbn import settings
from nxtbn.filemanager.models import Image, Document


from PIL import Image as PILImage
from io import BytesIO
from django.core.files.base import ContentFile


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = "__all__"
        read_only_fields = ("id", "created_by", "last_modified_by")

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["created_by"] = request.user
        validated_data["last_modified_by"] = request.user

        # Optimize the image before saving
        if "image" in validated_data:
            validated_data["image"] = self.optimize_image(validated_data["image"])
            validated_data["image_xs"] = self.optimize_image(validated_data["image"], max_size_kb=1, format="png", max_dimension=50)
        
        return super().create(validated_data)

    def update(self, instance, validated_data):
        request = self.context["request"]
        validated_data["last_modified_by"] = request.user

        # Optimize the image if it is being updated
        if "image" in validated_data:
            validated_data["image"] = self.optimize_image(validated_data["image"])
        
        return super().update(instance, validated_data)

    @staticmethod
    def optimize_image(image_file, max_size_kb=settings.IMAGE_COMPRESS_MAX, format="WEBP", max_dimension=800):
        """
        Optimize an image by resizing and converting it to the specified format while maintaining the aspect ratio.
        Ensures the image file size is below max_size_kb.
        """
        img = PILImage.open(image_file)
        img = img.convert("RGB")  # Convert to RGB for compatibility

        # Adjust dimension based on image type (smaller for PNG to ensure < 2023 bytes)
        if format.lower() == "png":
            max_dimension = 64  # Reduce size for PNG to keep it small

        img.thumbnail((max_dimension, max_dimension), PILImage.Resampling.LANCZOS)

        # Use a buffer to store the optimized image
        buffer = BytesIO()

        if format.lower() == "png":
            # Reduce colors using quantization (important for PNG)
            img = img.convert("P", palette=PILImage.ADAPTIVE, colors=32)  # Limit colors to 32
            img.save(buffer, format="PNG", optimize=True)
        else:
            quality = 85
            img.save(buffer, format=format, optimize=True, quality=quality)

            # Reduce quality iteratively for WebP/JPEG if size is too large
            while buffer.tell() > max_size_kb * 1024 and quality > 10:
                quality -= 5
                buffer = BytesIO()  # Reset buffer
                img.save(buffer, format=format, optimize=True, quality=quality)

        buffer.seek(0)

        # Return the new image as a ContentFile
        return ContentFile(buffer.read(), name=f"{image_file.name.split('.')[0]}.{format.lower()}")




class DocumentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Document
        fields = "__all__"
        read_only_fields = (
            "id",
            "created_by",
            "last_modified_by",
        )

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        validated_data["last_modified_by"] = self.context["request"].user
        return super().create(validated_data)
