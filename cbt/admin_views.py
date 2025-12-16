from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.urls import reverse
import json

from .forms import BulkQuestionUploadForm
from .models import Question, Choice, Subject, Exam


@staff_member_required
@require_http_methods(["GET", "POST"])
def bulk_upload_questions_admin(request):
    """Admin view for bulk uploading questions"""
    
    if request.method == 'POST':
        form = BulkQuestionUploadForm(request.POST)
        
        if form.is_valid():
            exam = form.cleaned_data['exam']
            subject = form.cleaned_data['subject']
            questions_data = form.cleaned_data['json_data']  # This is already parsed as list
            
            # Verify subject belongs to selected exam
            if subject.exam != exam:
                messages.error(request, 'Selected subject does not belong to the selected exam')
                return render(request, 'cbt/bulk_upload_admin.html', {'form': form})
            
            created_count = 0
            error_count = 0
            error_messages = []
            
            try:
                for idx, q_data in enumerate(questions_data, 1):
                    try:
                        question_text = q_data.get('question_text', '').strip()
                        options = q_data.get('options', {})
                        correct_answer = q_data.get('correct_answer', '').strip().upper()
                        explanation = q_data.get('explanation', '').strip()
                        
                        # Validate required fields
                        if not question_text:
                            error_messages.append(f'Question {idx}: Missing question_text')
                            error_count += 1
                            continue
                        
                        if not isinstance(options, dict):
                            error_messages.append(f'Question {idx}: Options must be an object (e.g., {{"A": "...", "B": "..."}})')
                            error_count += 1
                            continue
                        
                        if len(options) < 2:
                            error_messages.append(f'Question {idx}: Must have at least 2 options')
                            error_count += 1
                            continue
                        
                        if not correct_answer:
                            error_messages.append(f'Question {idx}: Missing correct_answer')
                            error_count += 1
                            continue
                        
                        if correct_answer not in options.keys():
                            error_messages.append(f'Question {idx}: correct_answer "{correct_answer}" not in options')
                            error_count += 1
                            continue
                        
                        # Create question
                        question = Question.objects.create(
                            subject=subject,
                            text=question_text,
                            creator=request.user
                        )
                        
                        # Create choices
                        for option_key, option_text in options.items():
                            is_correct = option_key.upper() == correct_answer
                            Choice.objects.create(
                                question=question,
                                text=str(option_text),
                                is_correct=is_correct
                            )
                        
                        created_count += 1
                        
                    except Exception as e:
                        error_messages.append(f'Question {idx}: {str(e)}')
                        if created_count > 0:  # Only delete if we started creating
                            # Clean up the question and its choices if error occurs
                            if 'question' in locals():
                                question.delete()
                        error_count += 1
                
                # Show results
                if created_count > 0:
                    messages.success(
                        request,
                        f'✓ Successfully created {created_count} question(s) in {subject.name}'
                    )
                
                if error_count > 0:
                    error_text = '\n'.join(error_messages[:10])  # Show first 10 errors
                    if len(error_messages) > 10:
                        error_text += f'\n\n... and {len(error_messages) - 10} more errors'
                    messages.warning(request, f'⚠ {error_count} question(s) failed:\n{error_text}')
                
                # Redirect to subject change page if successful
                if created_count > 0:
                    return redirect(f'{reverse("admin:cbt_subject_change", args=[subject.id])}')
                
            except Exception as e:
                messages.error(request, f'Bulk upload failed: {str(e)}')
        else:
            # Form has errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = BulkQuestionUploadForm()
    
    return render(request, 'cbt/bulk_upload_admin.html', {
        'form': form,
        'title': 'Bulk Upload Questions',
        'opts': Question._meta,
    })
