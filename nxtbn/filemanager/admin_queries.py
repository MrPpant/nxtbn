from django.conf import settings
import graphene
from graphql import GraphQLError
from graphene_django.filter import DjangoFilterConnectionField
from nxtbn.filemanager.models import Image
from nxtbn.filemanager.admin_types import ImageType


class ImageQuery(graphene.ObjectType):
    images = DjangoFilterConnectionField(ImageType)
    image = graphene.Field(ImageType, id=graphene.ID(required=True))

    def resolve_images(self, info, **kwargs):
        return Image.objects.all().order_by('-created_at')
    
    def resolve_image(self, info, id):
        try:
            return Image.objects.get(id=id)
        except Image.DoesNotExist:
            return None