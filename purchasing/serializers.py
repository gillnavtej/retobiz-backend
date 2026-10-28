from decimal import Decimal

from rest_framework import serializers

from .models import Purchase, PurchaseItem, Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "gstin", "phone"]


class PurchaseItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PurchaseItem
        fields = ["id", "product_id", "quantity", "purchase_rate", "line_total"]


class PurchaseSerializer(serializers.ModelSerializer):
    supplier_id = serializers.IntegerField(read_only=True)
    items = PurchaseItemSerializer(many=True, read_only=True)

    class Meta:
        model = Purchase
        fields = ["id", "reference", "supplier_id", "total_amount", "created_at", "items"]


class PurchaseItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    purchase_rate = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))


class PurchaseInputSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=100)
    supplier_id = serializers.IntegerField()
    items = PurchaseItemInputSerializer(many=True, allow_empty=False)

    def validate_items(self, items):
        ids = [i["product_id"] for i in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each product may appear only once per purchase.")
        return items
