    // Only auto-refresh on the job listing page
    if (window.location.pathname === '/admin/jobqueue/job/') {
        function autoRefreshPage() {
            window.location = window.location.href;
        }
        setInterval('autoRefreshPage()', 10000); // Refreshes every 10 seconds (10000 milliseconds)
    }
