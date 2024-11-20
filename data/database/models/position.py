class Position(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    pool = models.CharField(max_length=42)
    entry_price = models.DecimalField(max_digits=30, decimal_places=18)
    amount = models.DecimalField(max_digits=30, decimal_places=18)
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20)
    
    class Meta:
        db_table = 'positions'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['pool', 'timestamp'])
        ]