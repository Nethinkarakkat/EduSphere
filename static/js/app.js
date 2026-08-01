// EduSphere Application JavaScript

// Toggle password visibility - globally accessible
window.togglePassword = function(inputId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);

    if (!input || !icon) {
        console.error("Password elements not found:", inputId, iconId);
        return;
    }

    if (input.type === "password") {
        input.type = "text";
        icon.classList.remove("bi-eye");
        icon.classList.add("bi-eye-slash");
    } else {
        input.type = "password";
        icon.classList.remove("bi-eye-slash");
        icon.classList.add("bi-eye");
    }
};
