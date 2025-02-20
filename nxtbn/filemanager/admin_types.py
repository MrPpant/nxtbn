from django.conf import settings
import graphene
from graphene_django import DjangoObjectType
from graphene import relay
from nxtbn.filemanager.models import Image


class ImageType(DjangoObjectType):
    db_id = graphene.Int(source='id')
    image = graphene.String()
    image_xs = graphene.String()

    def resolve_image(self, info):
        return self.get_image_url(info.context)
    
    def resolve_image_xs(self, info):
        return self.get_image_xs_url(info.context)

    class Meta:
        model = Image
        fields = (
            'id',
            'name',
            'image',
            'image_xs',
            'created_at',
            'last_modified',
        )
        interfaces = (relay.Node, )
        filter_fields = {
            'name': ['exact', 'icontains'],
        }