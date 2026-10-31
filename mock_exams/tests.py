from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch, Mock
import requests

from .models import (
    CustomMockExam, MockExamSubject, MockExamQuestion, MockExamOption,
    MockExamFee, MockExamAttempt, MockExamResult, MockExamActivityLog,
    MockExamExternalPlatform
)
from courses.models import ActivationUnlock

User = get_user_model()


class MockExamIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username='admin_tester',
            email='admin@tester.com',
            password='testpassword123'
        )
        self.student = User.objects.create_user(
            username='student_tester',
            email='student@tester.com',
            password='testpassword123'
        )
        self.platform = MockExamExternalPlatform.objects.create(
            platform_name='JAMB Official',
            platform_type='jamb',
            platform_url='https://api.jamb.gov.ng',
            api_endpoint='/v1/mock-exams/stream',
            api_key='test_jamb_key',
            api_secret='test_jamb_secret',
            is_active=True,
            sync_enabled=True,
        )

    @patch('requests.get')
    def test_test_connection_success(self, mock_get):
        """Test outbound test-connection success"""
        self.client.force_authenticate(user=self.admin)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # Test both kebab-case and snake_case endpoints
        for url in [
            f'/api/mock-exams/admin/platforms/{self.platform.id}/test-connection/',
            f'/api/mock-exams/platforms/{self.platform.id}/test-connection/',
            f'/api/mock-exams/admin/platforms/{self.platform.id}/test_connection/',
        ]:
            response = self.client.post(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['status'], 'success')
            self.assertEqual(response.data['message'], 'Connection test successful!')
            self.assertEqual(response.data['http_status'], 200)

        # Verify outbound call arguments
        mock_get.assert_called_with(
            'https://api.jamb.gov.ng/v1/mock-exams/stream',
            headers={
                'Accept': 'application/json',
                'Authorization': 'Bearer test_jamb_key',
                'X-API-Key': 'test_jamb_key',
                'X-API-Secret': 'test_jamb_secret',
            },
            timeout=10
        )

    @patch('requests.get')
    def test_test_connection_timeout(self, mock_get):
        """Test test-connection handling outbound timeout"""
        self.client.force_authenticate(user=self.admin)
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        response = self.client.post(f'/api/mock-exams/admin/platforms/{self.platform.id}/test-connection/')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('timed out', response.data['message'])

    @patch('requests.get')
    def test_sync_exams_disabled_check(self, mock_get):
        """Test sync_exams fails if platform is inactive or sync is disabled"""
        self.client.force_authenticate(user=self.admin)
        self.platform.sync_enabled = False
        self.platform.save()

        response = self.client.post(f'/api/mock-exams/admin/platforms/{self.platform.id}/sync-exams/')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('disabled', response.data['message'])

    @patch('requests.get')
    def test_sync_exams_pipeline_success(self, mock_get):
        """Test full sync pipeline with streaming payload from user request"""
        self.client.force_authenticate(user=self.admin)

        sample_payload = {
            "status": "success",
            "platform": "JAMB",
            "exam": {
                "external_id": "jamb_utme_2026_mock_01",
                "title": "JAMB UTME 2026 Standard Mock Exam",
                "category": "JAMB",
                "duration": 60,
                "total_marks": 100,
                "is_active": True
            },
            "questions": [
                {
                    "id": "ext_q_001",
                    "subject": "Physics",
                    "question": "A car accelerates uniformly from rest at 4 m/s². What is the distance covered in the 5th second?",
                    "options": [
                        { "key": "A", "text": "18 m", "is_correct": True },
                        { "key": "B", "text": "50 m", "is_correct": False },
                        { "key": "C", "text": "10 m", "is_correct": False },
                        { "key": "D", "text": "20 m", "is_correct": False }
                    ],
                    "answer": "A",
                    "explanation": "Distance in the nth second: S_n = u + a/2(2n - 1) = 0 + (4/2)(2*5 - 1) = 2(9) = 18 m."
                }
            ]
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_payload
        mock_get.return_value = mock_response

        response = self.client.post(f'/api/mock-exams/admin/platforms/{self.platform.id}/sync-exams/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['synced_exams'], 1)
        self.assertEqual(response.data['synced_questions'], 1)

        # Check DB updates
        self.platform.refresh_from_db()
        self.assertIsNotNone(self.platform.last_sync_time)

        # Check Exam
        exam = CustomMockExam.objects.get(external_exam_id="jamb_utme_2026_mock_01")
        self.assertEqual(exam.title, "JAMB UTME 2026 Standard Mock Exam")
        self.assertTrue(exam.is_streaming)
        self.assertEqual(exam.total_duration_minutes, 60)
        self.assertEqual(exam.total_marks, 100)
        self.assertEqual(exam.status, 'published')

        # Check Subject
        subject = exam.subjects.first()
        self.assertIsNotNone(subject)
        self.assertEqual(subject.subject_name, "Physics")
        self.assertEqual(subject.num_questions, 1)

        # Check Question
        question = subject.questions.first()
        self.assertIsNotNone(question)
        self.assertIn("A car accelerates", question.question_text)
        self.assertEqual(question.explanation, sample_payload["questions"][0]["explanation"])

        # Check Options (A, B, C, D)
        options = question.options.all().order_by('order')
        self.assertEqual(options.count(), 4)
        opt_a = options.filter(option_letter='A').first()
        self.assertTrue(opt_a.is_correct)
        self.assertEqual(opt_a.option_text, "18 m")

        opt_b = options.filter(option_letter='B').first()
        self.assertFalse(opt_b.is_correct)
        self.assertEqual(opt_b.option_text, "50 m")

        # Check activity log
        log = MockExamActivityLog.objects.filter(action='sync_platform').first()
        self.assertIsNotNone(log)
        self.assertIn("JAMB Official", log.description)

    def test_fee_upsert_configuration(self):
        """Test admin fee creation and update for an exam"""
        self.client.force_authenticate(user=self.admin)
        exam = CustomMockExam.objects.create(
            title="Fee Test Exam",
            total_duration_minutes=60,
            total_marks=100
        )

        # 1. Create fee
        res1 = self.client.post('/api/mock-exams/admin/fees/', {
            'mock_exam': exam.id,
            'fee_amount': 2500,
            'discount_percentage': 10,
            'currency': 'NGN'
        })
        self.assertEqual(res1.status_code, 201)
        self.assertEqual(float(res1.data['fee_amount']), 2500.0)

        # 2. Update fee via POST (upsert)
        res2 = self.client.post('/api/mock-exams/admin/fees/', {
            'mock_exam': exam.id,
            'fee_amount': 3000,
            'discount_percentage': 20,
            'currency': 'NGN'
        })
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(float(res2.data['fee_amount']), 3000.0)

        exam.refresh_from_db()
        self.assertEqual(float(exam.fee.fee_amount), 3000.0)

    def test_student_unlock_and_attempt_flow(self):
        """Test student unlock verification, payment unlock, starting attempt, and submission"""
        exam = CustomMockExam.objects.create(
            title="Student CBT Mock Exam",
            total_duration_minutes=60,
            total_marks=10,
            passing_marks=5,
            is_published=True,
            is_active=True
        )
        MockExamFee.objects.create(mock_exam=exam, fee_amount=1500, currency='NGN')
        subject = MockExamSubject.objects.create(mock_exam=exam, subject_name='Math', num_questions=1)
        question = MockExamQuestion.objects.create(
            subject=subject,
            question_text="2 + 2 = ?",
            marks=10
        )
        opt_a = question.options.filter(option_letter='A').first()
        opt_a.option_text = '4'
        opt_a.is_correct = True
        opt_a.save()

        opt_b = question.options.filter(option_letter='B').first()
        opt_b.option_text = '5'
        opt_b.is_correct = False
        opt_b.save()

        self.client.force_authenticate(user=self.student)

        # 1. Check unlock status (should require payment)
        chk1 = self.client.post(f'/api/mock-exams/student/exams/{exam.id}/check_unlock_status/')
        self.assertEqual(chk1.status_code, 200)
        self.assertFalse(chk1.data['unlocked'])
        self.assertEqual(chk1.data['reason'], 'requires_payment')

        # 2. Unlock the exam
        unlock_res = self.client.post(f'/api/mock-exams/student/exams/{exam.id}/unlock/')
        self.assertEqual(unlock_res.status_code, 200)
        self.assertTrue(unlock_res.data['unlocked'])

        # 3. Check unlock status again (now unlocked)
        chk2 = self.client.post(f'/api/mock-exams/student/exams/{exam.id}/check_unlock_status/')
        self.assertEqual(chk2.status_code, 200)
        self.assertTrue(chk2.data['unlocked'])

        # 4. Start attempt
        start_res = self.client.post('/api/mock-exams/student/attempts/', {
            'mock_exam': exam.id
        })
        self.assertEqual(start_res.status_code, 201)
        attempt_id = start_res.data['id']

        # 5. Submit attempt with correct answer (format='json')
        submit_res = self.client.post(
            f'/api/mock-exams/student/attempts/{attempt_id}/submit/',
            {
                'answers': {str(question.id): opt_a.id},
                'time_spent': 45
            },
            format='json'
        )
        self.assertEqual(submit_res.status_code, 200)
        self.assertEqual(float(submit_res.data['obtained_marks']), 10.0)
        self.assertEqual(float(submit_res.data['percentage']), 100.0)
        self.assertEqual(submit_res.data['grade'], 'A')
        self.assertTrue(submit_res.data['passed'])
        self.assertEqual(submit_res.data['status'], 'completed')

        # Verify results in serializer
        results = submit_res.data['results']
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['is_correct'])
        self.assertEqual(results[0]['selected_option_id'], opt_a.id)
