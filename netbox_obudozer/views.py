from netbox.views import generic
from . import models, forms, tables, filtersets


class VMRecordListView(generic.ObjectListView):
    queryset = models.VMRecord.objects.all()
    table = tables.VMRecordTable
    filterset = filtersets.VMRecordFilterSet


class VMRecordView(generic.ObjectView):
    queryset = models.VMRecord.objects.all()


class VMRecordEditView(generic.ObjectEditView):
    queryset = models.VMRecord.objects.all()
    form = forms.VMRecordForm


class VMRecordDeleteView(generic.ObjectDeleteView):
    queryset = models.VMRecord.objects.all()


class VMRecordBulkDeleteView(generic.BulkDeleteView):
    queryset = models.VMRecord.objects.all()
    table = tables.VMRecordTable
