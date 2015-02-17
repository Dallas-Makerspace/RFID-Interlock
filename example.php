<?php
if (isset($_GET['tag'])) {
    if ($_GET['tag'] == 2707938) {
        // Authorize activation
        http_response_code(204);
    } else {
        // Don't authorize activation
        http_response_code(403);
    }
} elseif (isset($_GET['status']) && $_GET['status'] == 'shutdown') {
    // log shutdown
}
// Do nothing, or whatever, I'm an example script not a cop
