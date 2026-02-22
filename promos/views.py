from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import PromoCode
from .serializers import PromoCodeSerializer
from decimal import Decimal


class PromoCodeViewSet(viewsets.ModelViewSet):
    queryset = PromoCode.objects.all()
    serializer_class = PromoCodeSerializer
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def apply(self, request):
        """Validate a promo code and return discount/new_total.

        POST payload: { code: str, total_amount: decimal, consume: bool (optional), payment_type: str (optional) }
        """
        data = request.data
        code = (data.get('code') or '').strip().upper()
        if not code:
            return Response({'detail': 'code required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            total = Decimal(str(data.get('total_amount', '0')))
        except Exception:
            return Response({'detail': 'invalid total_amount'}, status=status.HTTP_400_BAD_REQUEST)

        promo = PromoCode.objects.filter(code=code).first()
        if not promo:
            return Response({'valid': False, 'detail': 'invalid code'}, status=status.HTTP_404_NOT_FOUND)
        if not promo.is_usable():
            return Response({'valid': False, 'detail': 'promo not usable/expired'}, status=status.HTTP_400_BAD_REQUEST)

        # Optional: check applicable_to against payment_type
        payment_type = data.get('payment_type')
        applicable = (promo.applicable_to or 'all')
        if applicable != 'all':
            # support encoded exam target like 'exam:<id>'
            if isinstance(applicable, str) and applicable.startswith('exam:'):
                target_exam = applicable.split(':', 1)[1]
                # try to extract exam id from request (either top-level or inside activation metadata)
                exam_id = data.get('exam_id') or (data.get('activation') and data.get('activation').get('exam_id'))
                if not exam_id or str(exam_id) != str(target_exam):
                    return Response({'valid': False, 'detail': 'promo not applicable for this payment type'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                # if promo is generic 'exam' (without id), accept activation payment_type
                if applicable == 'exam':
                    if payment_type != 'activation':
                        return Response({'valid': False, 'detail': 'promo not applicable for this payment type'}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    if payment_type:
                        if applicable != payment_type:
                            return Response({'valid': False, 'detail': 'promo not applicable for this payment type'}, status=status.HTTP_400_BAD_REQUEST)
                    else:
                        return Response({'valid': False, 'detail': 'promo not applicable for this payment type'}, status=status.HTTP_400_BAD_REQUEST)

        discount = promo.compute_discount(total)
        new_total = max(Decimal('0.00'), (total - discount))

        # consume if requested
        if data.get('consume'):
            try:
                promo.consume()
            except Exception as e:
                return Response({'valid': False, 'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'valid': True, 'discount': str(discount), 'new_total': str(new_total), 'promo': PromoCodeSerializer(promo, context={'request': request}).data})
