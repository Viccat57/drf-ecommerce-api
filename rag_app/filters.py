from django_filters import rest_framework as df
from .models import Brand, Category, Product


class ProductFilter(df.FilterSet):
    brand = df.ModelChoiceFilter(queryset=Brand.objects.all())
    category = df.ModelChoiceFilter(
        queryset=Category.objects.all(),
        method="filter_category",
    )
    min_price = df.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = df.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = df.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = Product
        fields = []

    def filter_category(self, queryset, name, value):
        ids = {value.pk}
        frontier = {value.pk}

        while frontier:
            children = set(
                Category.objects.filter(parent_id__in=frontier)
                .exclude(pk__in=ids)
                .values_list("pk", flat=True)
            )
            ids.update(children)
            frontier = children

        return queryset.filter(category_id__in=ids)

    def filter_in_stock(self, queryset, name, value):
        if value is None:
            return queryset

        if value:
            return queryset.filter(stock__gt=0)

        return queryset.filter(stock=0)