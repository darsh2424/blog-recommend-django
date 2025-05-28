// Common JS
function toggleLeftSidebar() {
    const sidebar = document.getElementById("leftSidebar");
    sidebar.classList.toggle("show");
}

function toggleRightSidebar() {
    const sidebar = document.getElementById("rightSidebar");
    sidebar.classList.toggle("show");
}

// Sidebar filter logic
document.addEventListener('DOMContentLoaded', function () {
    const input = document.getElementById('filterInput');
    if (input) {
        input.addEventListener('keyup', function () {
            const query = this.value.toLowerCase();
            document.querySelectorAll('#filterList li').forEach(li => {
                li.style.display = li.textContent.toLowerCase().includes(query) ? 'block' : 'none';
            });
        });
    }
});

