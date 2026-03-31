from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AggregateViewSet, DerivationRuleViewSet

router = DefaultRouter()
router.register('', AggregateViewSet, basename='aggregates')
router.register('derivation-rules', DerivationRuleViewSet, basename='aggregate-derivation-rules')

urlpatterns = [
    path('', include(router.urls)),
]
