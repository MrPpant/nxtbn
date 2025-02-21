from django.db import models

from nxtbn.core.models import AbstractBaseModel
from nxtbn.users.admin import User


class Image(AbstractBaseModel):
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='image_created')
    last_modified_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='image_modified', null=True, blank=True)
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='images/')
    image_xs = models.ImageField(upload_to='images/xs/', null=True, blank=True)
    image_alt_text = models.CharField(max_length=255)

    def get_image_url(self,request):
        if self.image:
            return request.build_absolute_uri(self.image.url)
        return None

    def get_image_xs_url(self,request):
        if self.image_xs:
            return request.build_absolute_uri(self.image_xs.url)
        
        if self.image:
            return request.build_absolute_uri(self.image.url)

        return None


class Document(AbstractBaseModel):
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='document_created')
    last_modified_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='document_modified', null=True, blank=True)
    name = models.CharField(max_length=255)
    document = models.FileField()
    image_alt_text = models.CharField(max_length=255)