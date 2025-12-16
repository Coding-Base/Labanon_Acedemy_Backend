from django import forms
from .models import Exam, Subject


class BulkQuestionUploadForm(forms.Form):
    """Form for uploading questions in bulk from admin panel"""
    
    exam = forms.ModelChoiceField(
        queryset=Exam.objects.all(),
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.all(),
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    json_data = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 15,
            'placeholder': '[{"question_text": "...", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, "correct_answer": "A", "explanation": "...", "subject": "Chemistry"}, ...]'
        }),
        help_text='Paste JSON array of questions with the format shown in the placeholder'
    )

    def clean_json_data(self):
        import json
        data = self.cleaned_data.get('json_data')
        try:
            questions = json.loads(data)
            if not isinstance(questions, list):
                raise forms.ValidationError('JSON data must be an array of questions')
            return questions
        except json.JSONDecodeError as e:
            raise forms.ValidationError(f'Invalid JSON: {str(e)}')
