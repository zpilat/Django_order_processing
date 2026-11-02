document.addEventListener('DOMContentLoaded', () => {
    const uvolneni = document.getElementById('id_uvolneni');
    const duvody = document.getElementById('duvody-neshody');
    const cistota = document.getElementById('id_cistota');
    const ulozeni = document.getElementById('id_ulozeni');
    const pravidlaElement = document.getElementById('pravidla-kontroly-bedny');
    if (!uvolneni || !duvody || !cistota || !ulozeni || !pravidlaElement) return;

    const pravidla = JSON.parse(pravidlaElement.textContent);
    const omezeniCistoty = document.getElementById('omezeni-cistoty');
    const omezeniUlozeni = document.getElementById('omezeni-ulozeni');
    const checkboxes = Array.from(duvody.querySelectorAll('input[type="checkbox"]'));
    const aktualizovat = () => {
        if (pravidla.can_edit) {
            const cistotaNok = cistota.value === 'NOK';
            const ulozeniNok = ulozeni.value === 'NOK';
            const povolene = cistotaNok || ulozeniNok ? ['NE'] : pravidla.povolene_stavy_prohybu;
            const puvodniVyber = uvolneni.value;
            const moznosti = pravidla.uvolneni.filter(([value]) => povolene.includes(value));
            uvolneni.replaceChildren(...moznosti.map(([value, label]) => new Option(label, value)));
            uvolneni.value = povolene.includes(puvodniVyber) ? puvodniVyber : moznosti[0][0];
            omezeniCistoty?.classList.toggle('d-none', !cistotaNok);
            omezeniUlozeni?.classList.toggle('d-none', !ulozeniNok);

            const automaticke = {
                neshoda_krivost: pravidla.krivost,
                neshoda_cistota: cistotaNok,
            };
            if (ulozeniNok) automaticke.neshoda_jine = true;
            const uvolneno = uvolneni.value === 'UV';
            checkboxes.forEach(checkbox => {
                const automaticky = Object.hasOwn(automaticke, checkbox.name);
                if (uvolneno) checkbox.checked = false;
                else if (automaticky) checkbox.checked = automaticke[checkbox.name];
                checkbox.disabled = uvolneno || automaticky;
            });
        }
        duvody.classList.toggle('d-none', !['NE', 'UO', 'UV'].includes(uvolneni.value));
    };

    uvolneni.addEventListener('change', aktualizovat);
    cistota.addEventListener('change', aktualizovat);
    ulozeni.addEventListener('change', aktualizovat);
    checkboxes.forEach(checkbox => checkbox.addEventListener('change', aktualizovat));
    aktualizovat();
});
