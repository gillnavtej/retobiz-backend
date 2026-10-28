from decimal import Decimal

from rest_framework import serializers

from .models import PriceOverrideApproval, Sale, SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    override_approval_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = SaleItem
        fields = [
            "id", "product_id", "quantity", "mrp_snapshot", "rate_applied", "gst_rate_snapshot",
            "taxable_value", "cgst", "sgst", "line_total", "override_approval_id",
        ]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "bill_no", "transaction_id", "subtotal", "tax_total", "grand_total",
            "status", "created_by", "created_at", "items",
        ]


class SaleItemInputSerializer(serializers.Serializer):
    # NOTE: no rate field. Unknown keys (e.g. a forged rate_applied) are ignored.
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    override_approval_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class SaleInputSerializer(serializers.Serializer):
    transaction_id = serializers.UUIDField()
    items = SaleItemInputSerializer(many=True, allow_empty=False)

    def validate_items(self, items):
        ids = [i["product_id"] for i in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each product may appear only once per bill.")
        return items


class PriceOverrideSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    approved_by = serializers.CharField(source="approved_by.username", read_only=True)
    used = serializers.SerializerMethodField()

    class Meta:
        model = PriceOverrideApproval
        fields = [
            "id", "product_id", "original_rate", "requested_rate", "reason",
            "approved_by", "created_at", "used_at", "used",
        ]

    def get_used(self, obj):
        return obj.used_at is not None


class PriceOverrideInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    requested_rate = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    reason = serializers.CharField(max_length=255)
