    function autoRefreshPage() {
        window.location = window.location.href;
    }
    setInterval('autoRefreshPage()', 10000); // Refreshes every 10 seconds (10000 milliseconds)