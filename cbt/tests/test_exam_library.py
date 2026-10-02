from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from subadmin.models import SubAdmin
from users.models import User

from cbt.models import Country, Exam, ExamFolder, Subject
from cbt.serializers import ExamFolderSerializer


class ExamLibraryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(username='library-student', password='password')
        self.admin = User.objects.create_user(
            username='library-admin', password='password', role=User.ADMIN
        )
        self.country = Country.objects.create(name='Testland', code='TL', slug='testland')
        self.folder = ExamFolder.objects.create(
            country=self.country, name='JAMB', slug='jamb'
        )

    def test_library_hides_drafts_from_students(self):
        Exam.objects.create(
            title='Published exam', slug='published-exam', folder=self.folder, status='published'
        )
        Exam.objects.create(
            title='Draft exam', slug='draft-exam', folder=self.folder, status='draft'
        )

        response = self.client.get('/api/cbt/library/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn('Published exam', str(body))
        self.assertNotIn('Draft exam', str(body))

    def test_student_cannot_mutate_exam_library(self):
        self.client.force_authenticate(self.student)

        response = self.client.post(
            '/api/cbt/countries/',
            {'name': 'Ghana', 'code': 'GH', 'slug': 'ghana'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_permitted_subadmin_can_mutate_exam_library(self):
        subadmin_user = User.objects.create_user(
            username='library-subadmin', password='password'
        )
        SubAdmin.objects.create(
            created_by=self.admin,
            user=subadmin_user,
            permissions={'can_manage_exams': True},
        )
        self.client.force_authenticate(subadmin_user)

        response = self.client.post(
            '/api/cbt/countries/',
            {'name': 'Ghana', 'code': 'GH', 'slug': 'ghana'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_folder_serializer_rejects_cross_country_parent_and_cycles(self):
        other_country = Country.objects.create(name='Ghana', code='GH', slug='ghana')
        other_folder = ExamFolder.objects.create(
            country=other_country, name='Other', slug='other'
        )
        child = ExamFolder.objects.create(
            country=self.country, parent=self.folder, name='Child', slug='child'
        )

        cross_country = ExamFolderSerializer(
            child,
            data={'country': self.country.id, 'parent': other_folder.id},
            partial=True,
        )
        self.assertFalse(cross_country.is_valid())

        cycle = ExamFolderSerializer(
            self.folder,
            data={'parent': child.id},
            partial=True,
        )
        self.assertFalse(cycle.is_valid())

    def test_folder_reorder_preserves_requested_sibling_order(self):
        second = ExamFolder.objects.create(
            country=self.country, name='Second', slug='second', sort_order=1
        )
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            '/api/cbt/folders/reorder/',
            {'items': [
                {'id': second.id, 'sort_order': 0},
                {'id': self.folder.id, 'sort_order': 1},
            ]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ExamFolder.objects.get(pk=second.id).sort_order, 0)
        self.assertEqual(ExamFolder.objects.get(pk=self.folder.id).sort_order, 1)

    def test_delete_with_subjects_archives_exam(self):
        exam = Exam.objects.create(
            title='Exam with content', slug='exam-with-content', folder=self.folder
        )
        Subject.objects.create(exam=exam, name='Mathematics')
        self.client.force_authenticate(self.admin)

        response = self.client.delete(f'/api/cbt/exams/{exam.id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        exam.refresh_from_db()
        self.assertEqual(exam.status, 'archived')
        self.assertFalse(exam.is_visible)
