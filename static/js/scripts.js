/**
 * AlumniLink - Client Side Scripts
 * Created exclusively for the IT Department Alumni Networking Platform
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Navigation Scroll Effect
    const navbar = document.getElementById('mainNavbar');
    
    if (navbar) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 50) {
                navbar.style.padding = '0.6rem 0';
                navbar.style.boxShadow = '0 10px 30px -10px rgba(0, 0, 0, 0.3)';
                navbar.style.backgroundColor = 'rgba(15, 23, 42, 0.95) !important';
            } else {
                navbar.style.padding = '1rem 0';
                navbar.style.boxShadow = 'none';
                navbar.style.backgroundColor = 'rgba(15, 23, 42, 0.9) !important';
            }
        });
    }

    // 2. Auto Dismiss Flash Alerts after 5 seconds
    const alerts = document.querySelectorAll('.premium-alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // 3. Log initial check for verification status
    console.log("AlumniLink: Base Platform Loaded Successfully. Privacy mode is active.");
});
