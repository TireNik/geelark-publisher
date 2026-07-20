from django import forms

class ExcelUploadForm(forms.Form):
    excel_file = forms.FileField(
        label='Excel файл',
        help_text='Загрузите Excel файл с расписанием публикаций',
        widget=forms.FileInput(attrs={'accept': '.xlsx,.xls'})
    )