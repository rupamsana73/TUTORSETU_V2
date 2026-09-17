"""API filters for tutor discovery."""
import django_filters

from tutors.models import TutorProfile


class TutorProfileFilter(django_filters.FilterSet):
    subject = django_filters.NumberFilter(field_name="subjects__id")
    class_level = django_filters.NumberFilter(field_name="classes__id")
    board = django_filters.NumberFilter(field_name="boards__id")
    location = django_filters.NumberFilter(field_name="city__id")
    verified = django_filters.BooleanFilter(method="filter_verified")
    fee_max = django_filters.NumberFilter(field_name="hourly_fee", lookup_expr="lte")
    fee_min = django_filters.NumberFilter(field_name="hourly_fee", lookup_expr="gte")
    min_experience = django_filters.NumberFilter(field_name="experience_years", lookup_expr="gte")
    min_rating = django_filters.NumberFilter(field_name="average_rating", lookup_expr="gte")
    weekday = django_filters.NumberFilter(field_name="availability__weekday")

    class Meta:
        model = TutorProfile
        fields = ("teaching_mode", "subject", "class_level", "board", "location")

    def filter_verified(self, queryset, name, value):
        if value:
            return queryset.filter(verification_status="VERIFIED")
        return queryset
