(() => {
    const scrollSidebarToEnd = () => {
        window.requestAnimationFrame(() => {
            const sidebar = document.getElementById('nav-sidebar');
            if (sidebar) {
                // Panel začíná pod hlavičkou, proto nemá k dispozici celou výšku okna.
                const top = Math.max(0, sidebar.getBoundingClientRect().top);
                sidebar.style.maxHeight = `${Math.max(0, window.innerHeight - top)}px`;
                sidebar.scrollTop = sidebar.scrollHeight;
            }
        });
    };

    window.addEventListener('pageshow', () => {
        scrollSidebarToEnd();
        if (document.fonts) {
            document.fonts.ready.then(scrollSidebarToEnd);
        }
    });
    window.addEventListener('resize', scrollSidebarToEnd);
})();
