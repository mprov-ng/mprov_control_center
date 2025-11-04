// Job Status Change Notifications
// This script polls for job status changes and displays toast notifications

(function() {
    'use strict';
    
    // Configuration constants
    const STORAGE_KEY = 'job_status_notified_changes';
    const MAX_TRACKED_CHANGES = 100;
    const MAX_VISIBLE_NOTIFICATIONS = 5; // Limit concurrent notifications
    
    // Load previously notified changes from localStorage
    let notifiedChanges = new Set();
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
            const parsed = JSON.parse(stored);
            // Only keep changes from the last 24 hours to prevent storage bloat
            const now = Date.now();
            const cutoff = now - (24 * 60 * 60 * 1000); // 24 hours in milliseconds
            
            Object.keys(parsed).forEach(key => {
                if (parsed[key] > cutoff) {
                    notifiedChanges.add(key);
                }
            });
        }
    } catch (e) {
        // If there's an error parsing localStorage, start fresh
        notifiedChanges = new Set();
    }
    
    // Save notified changes to localStorage
    function saveNotifiedChanges() {
        try {
            const now = Date.now();
            const toStore = {};
            for (const changeId of notifiedChanges) {
                toStore[changeId] = now;
            }
            localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore));
        } catch (e) {
            // If localStorage fails, continue without persistence
            console.warn('Failed to save notified changes to localStorage', e);
        }
    }
    
    // Function to create and show a toast notification
    function showToast(jobName, oldStatus, newStatus) {
        // Create toast container if it doesn't exist
        let toastContainer = document.getElementById('job-toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'job-toast-container';
            toastContainer.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 9999;
                width: 350px;
            `;
            document.body.appendChild(toastContainer);
        }
        
        // Check if we've reached the maximum number of visible notifications
        const currentToasts = toastContainer.querySelectorAll('[id^="toast-"]');
        if (currentToasts.length >= MAX_VISIBLE_NOTIFICATIONS) {
            // Remove the oldest notification to make room for the new one
            const oldestToast = currentToasts[0];
            if (oldestToast && oldestToast.parentNode) {
                oldestToast.parentNode.removeChild(oldestToast);
            }
        }
        
        // Create toast element
        const toastId = 'toast-' + Date.now();
        const toast = document.createElement('div');
        toast.id = toastId;
        toast.style.cssText = `
            background: #fff;
            border-left: 4px solid #007bff;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            margin-bottom: 10px;
            padding: 15px;
            position: relative;
            transform: translateX(100%);
            transition: transform 0.3s ease-in-out;
        `;
        
        // Add content to toast
        toast.innerHTML = `
            <div style="font-weight: bold; margin-bottom: 5px;">Job Status Changed</div>
            <div style="font-size: 14px;">
                <strong>${jobName}</strong><br>
                ${oldStatus} → ${newStatus}
            </div>
            <button style="
                background: none;
                border: none;
                color: #999;
                cursor: pointer;
                font-size: 18px;
                line-height: 1;
                position: absolute;
                right: 10px;
                top: 5px;
            ">&times;</button>
        `;
        
        // Add toast to container
        toastContainer.appendChild(toast);
        
        // Trigger entrance animation
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 10);
        
        // Add close functionality
        const closeButton = toast.querySelector('button');
        closeButton.addEventListener('click', function() {
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        });
        
        // Auto dismiss after 5 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.style.transform = 'translateX(100%)';
                setTimeout(() => {
                    if (toast.parentNode) {
                        toast.parentNode.removeChild(toast);
                    }
                }, 300);
            }
        }, 5000);
    }
    
    // Function to poll for job status changes
    function pollJobStatusChanges() {
        // Use the globally defined URL if available, otherwise fallback to hardcoded path
        let url = typeof JOB_STATUS_CHANGES_URL !== 'undefined' ? JOB_STATUS_CHANGES_URL : '/jobqueue/status-changes/';
        
        // Also check for Django-provided URL in context
        if (typeof django !== 'undefined' && django.job_status_changes_url) {
            url = django.job_status_changes_url;
        }
        
        fetch(url)
            .then(response => response.json())
            .then(data => {
                if (data.changes && data.changes.length > 0) {
                    data.changes.forEach(change => {
                        // Create a unique identifier for this change
                        const changeId = `${change.job_id}-${change.timestamp}`;
                        
                        // Only show notification if we haven't already shown it
                        if (!notifiedChanges.has(changeId)) {
                            showToast(
                                change.job_name,
                                change.old_status,
                                change.new_status
                            );
                            
                            // Mark as notified
                            notifiedChanges.add(changeId);
                            
                            // Save to localStorage for persistence across page navigations
                            saveNotifiedChanges();
                            
                            // Limit the size of our tracking set
                            if (notifiedChanges.size > MAX_TRACKED_CHANGES) {
                                const firstKey = notifiedChanges.values().next().value;
                                notifiedChanges.delete(firstKey);
                                // Save after deletion to keep localStorage in sync
                                saveNotifiedChanges();
                            }
                        }
                    });
                }
            })
            .catch(error => {
                console.log('Error polling for job status changes:', error);
            });
    }
    
    // Start polling when the page loads
    document.addEventListener('DOMContentLoaded', function() {
        // Only run on admin pages
        if (document.querySelector('.admin-interface, .admin-site, #changelist')) {
            // Poll every 5 seconds
            setInterval(pollJobStatusChanges, 1000);
        }
    });
    
})();
