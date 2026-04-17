import factory
from factory.django import DjangoModelFactory

from apps.assessments.models import Resource


class ResourceFactory(DjangoModelFactory):
    class Meta:
        model = Resource

    assignment = factory.SubFactory(
        'tests.factories.academics_factory.TeacherCourseAssignmentFactory'
    )
    title = factory.Sequence(lambda n: f'Resource {n}')
    resource_type = Resource.VIDEO_LINK
    url = factory.Sequence(lambda n: f'https://www.youtube.com/watch?v=test{n:06d}')
    file = None


class PDFResourceFactory(ResourceFactory):
    resource_type = Resource.PDF
    url = None
    file = factory.django.FileField(filename='test.pdf', data=b'%PDF-1.4 fake pdf')
