from celery import shared_task
from PIL import Image
from django.core.files.base import ContentFile
from io import BytesIO
import os

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
)
def compress_model_image(self, app_label, model_name, object_id, field_name):
    from django.apps import apps

    Model = apps.get_model(app_label, model_name)
    obj = Model.objects.get(id=object_id)

    image_field = getattr(obj, field_name)
    if not image_field:
        return

    img = Image.open(image_field)
    img = img.convert("RGB")
    img.thumbnail((1600, 1600))

    buffer = BytesIO()
    img.save(
        buffer,
        format="JPEG",
        optimize=True,
        quality=70
    )

    filename = os.path.basename(image_field.name)
    image_field.save(filename, ContentFile(buffer.getvalue()), save=True)
    buffer.close()
