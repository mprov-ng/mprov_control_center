from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.contrib.sessions.models import Session
from .models import Job
import json
import time

# Dictionary to store old status values during pre_save
_old_statuses = {}

@receiver(pre_save, sender=Job)
def job_pre_save(sender, instance, **kwargs):
    """
    Signal handler that captures the old status before saving.
    """
    if instance.pk:  # Only for existing instances
        try:
            old_instance = Job.objects.get(pk=instance.pk)
            # Store the old status ID for this instance
            _old_statuses[instance.pk] = old_instance.status_id
        except Job.DoesNotExist:
            pass

@receiver(post_save, sender=Job)
def job_status_changed(sender, instance, created, **kwargs):
    """
    Signal handler that detects when a job's status changes.
    Stores the change information for display as a toast notification.
    """
    # Skip newly created jobs, we only care about status changes
    if created:
        return
    
    # Get the old status from our storage
    old_status_id = _old_statuses.pop(instance.pk, None)
    
    # If we don't have the old status, we can't compare
    if old_status_id is None:
        return
    
    # Check if status actually changed
    if old_status_id != instance.status_id:
        # We need to get the status names, so we need to fetch the status objects
        try:
            from django.core.cache import cache
            
            # Get the old and new status names
            old_status = instance.__class__.status.field.related_model.objects.get(pk=old_status_id)
            new_status = instance.status
            
            # Create a unique key for this change
            change_key = f"job_status_change_{instance.pk}_{int(time.time())}"
            
            # Store the change information
            change_data = {
                'job_id': instance.pk,
                'job_name': instance.name,
                'old_status': old_status.name,
                'new_status': new_status.name,
                'timestamp': int(time.time())
            }
            
            # Store in cache for 5 minutes (should be plenty for notification display)
            cache.set(change_key, change_data, 300)
            
            # Also store a list of recent changes for easy retrieval
            recent_changes_key = "recent_job_status_changes"
            recent_changes = cache.get(recent_changes_key, [])
            
            # Add this change to the recent changes list
            recent_changes.append(change_key)
            
            # Keep only the last 50 changes to prevent memory issues
            if len(recent_changes) > 50:
                # Remove oldest entries
                removed_keys = recent_changes[:-50]
                recent_changes = recent_changes[-50:]
                # Clean up removed keys from cache
                cache.delete_many(removed_keys)
            
            # Store the updated recent changes list
            cache.set(recent_changes_key, recent_changes, 300)
        except Exception:
            # If there's any error, just clean up and continue
            pass
