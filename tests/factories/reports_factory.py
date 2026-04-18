import factory
from factory.django import DjangoModelFactory

from apps.reports.models import ReportTask


class ReportTaskFactory(DjangoModelFactory):
    class Meta:
        model = ReportTask

    requested_by = factory.SubFactory('tests.factories.user_factory.UserFactory', role='ADMIN')
    report_type = ReportTask.ACADEMIC_PERFORMANCE
    format = ReportTask.CSV
    filters = factory.LazyFunction(dict)
    status = ReportTask.PENDING
    download_url = None
    error_message = None
