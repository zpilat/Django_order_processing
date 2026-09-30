document.addEventListener('DOMContentLoaded', () => {
    const uvolneni = document.getElementById('id_uvolneni');
    const duvody = document.getElementById('duvody-neshody');
    if (!uvolneni || !duvody) return;

    const checkboxes = Array.from(duvody.querySelectorAll('input[type="checkbox"]'));
    const aktualizovatViditelnost = () => {
        const zobrazit = uvolneni.value === 'NE' || checkboxes.some(checkbox => checkbox.checked);
        duvody.classList.toggle('d-none', !zobrazit);
    };

    uvolneni.addEventListener('change', aktualizovatViditelnost);
    checkboxes.forEach(checkbox => checkbox.addEventListener('change', aktualizovatViditelnost));
    aktualizovatViditelnost();
});
