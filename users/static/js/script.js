// Common JS
function toggleLeftSidebar() {
    const sidebar = document.getElementById("leftSidebar");
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

//follow
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.follow-btn').forEach(button => {
        button.addEventListener('click', function() {
            const username = this.dataset.username;
            const url = this.dataset.followUrl;
            const csrf = this.dataset.csrf;
            const isFollowing = this.classList.contains('following');
            const action = isFollowing ? 'unfollow' : 'follow';
            
            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrf,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: `action=${action}`
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    this.classList.toggle('following');
                    if (data.followed) {
                        this.innerHTML = '<i class="fas fa-user-minus"></i> Unfollow';
                    } else {
                        this.innerHTML = '<i class="fas fa-user-plus"></i> Follow';
                    }
                    // Update follower count if needed
                    const followerCountEl = document.querySelector('.follower-count');
                    if (followerCountEl && data.follower_count !== undefined) {
                        followerCountEl.textContent = data.follower_count;
                    }
                }
            })
            .catch(error => console.error('Error:', error));
        });
    });
});

