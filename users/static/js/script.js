// Common JS
function toggleDarkMode() {
    document.body.classList.toggle("dark-mode");
}

// Sidebar Toggle
document.getElementById("sidebarToggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("active");
});
document.getElementById("closeSidebar").addEventListener("click", () => {
    document.getElementById("sidebar").classList.remove("active");
});
