document.addEventListener('DOMContentLoaded', function () {
  // Initialize Select2 on the shareUsers dropdown
  $('#shareUsers').select2({
    data: allUsers.map(user => ({
      id: user.id,
      text: user.username
    })),
    placeholder: "Type to search users...",
    width: '100%'
  });

  // Prevent selecting current user or users already shared with
  $('#shareUsers').on('select2:select', function (e) {
    const selectedId = e.params.data.id;
    const selectedUsername = allUsers.find(u => u.id === selectedId)?.username;

    // Check if selected user is current user or already shared with
    const isInvalid = selectedId === currentUser || Object.values(sharedMap).flat().includes(selectedUsername);

    if (isInvalid) {
      // Remove invalid selection
      let selected = $('#shareUsers').val();
      selected = selected.filter(val => val !== selectedId.toString());
      $('#shareUsers').val(selected).trigger('change');
      alert("You cannot share with yourself or users you've already shared this match with.");
    }
  });

  // Clear All selections
  document.getElementById('clearUsers')?.addEventListener('click', () => {
    $('#shareUsers').val(null).trigger('change');
  });
});
