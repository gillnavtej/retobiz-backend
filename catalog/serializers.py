from decimal import Decimal

from rest_framework import serializers

from common.exceptions import DuplicateBarcode

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    mrp = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    purchase_rate = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    selling_rate = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    gst_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("28")
    )

    class Meta:
        model = Product
        fields = [
            "id", "name", "barcode", "mrp", "purchase_rate", "selling_rate", "gst_rate",
            "stock_qty", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "stock_qty", "created_at", "updated_at"]

    def validate(self, attrs):
        mrp = attrs.get("mrp", getattr(self.instance, "mrp", None))
        selling = attrs.get("selling_rate", getattr(self.instance, "selling_rate", None))
        if mrp is not None and selling is not None and selling > mrp:
            raise serializers.ValidationError({"selling_rate": "Selling rate cannot exceed MRP."})
        store = self.context["request"].user.store
        barcode = attrs.get("barcode")
        if barcode is not None:
            qs = Product.objects.filter(store=store, barcode=barcode)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise DuplicateBarcode()
        return attrs
