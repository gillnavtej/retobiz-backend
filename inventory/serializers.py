from rest_framework import serializers

from .models import StockMovement


class StockMovementSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id", "product_id", "movement_type", "quantity_delta", "balance_after",
            "reference_type", "reference_id", "transaction_ref", "reason", "created_by", "created_at",
        ]


class StockAdjustmentInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity_delta = serializers.IntegerField()
    reason = serializers.CharField(max_length=255)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def validate_quantity_delta(self, v):
        if v == 0:
            raise serializers.ValidationError("Quantity delta cannot be zero.")
        return v
