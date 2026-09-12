const API_URL = '/api/users';
const $ = (id) => document.getElementById(id);

function setState(message = '', error = false) {
  $('status').textContent = message;
  $('errorState').classList.toggle('hidden', !error);
  $('errorState').textContent = error ? message : '';
}

async function loadUsers() {
  setState('Loading users…'); $('emptyState').classList.add('hidden');
  try {
    const query = $('searchInput').value.trim();
    const response = await fetch(`${API_URL}?search=${encodeURIComponent(query)}`);
    if (!response.ok) throw new Error('Unable to load users.');
    displayUsers(await response.json()); setState('');
  } catch (error) { $('userTableBody').innerHTML = ''; setState(error.message, true); }
}

function displayUsers(users) {
  const body = $('userTableBody'); body.innerHTML = '';
  $('emptyState').classList.toggle('hidden', users.length !== 0);
  users.forEach(user => { const row = document.createElement('tr'); [user.id, user.name, user.email].forEach(value => { const cell = document.createElement('td'); cell.textContent = value; row.appendChild(cell); }); body.appendChild(row); });
}

async function send(url, options, success) {
  setState('Saving…');
  try { const response = await fetch(url, options); if (!response.ok) { const detail = await response.json(); throw new Error(detail.detail || 'Request failed.'); } await success(response); await loadUsers(); }
  catch (error) { setState(error.message, true); }
}

$('searchButton').addEventListener('click', loadUsers);
$('clearButton').addEventListener('click', () => { $('searchInput').value = ''; loadUsers(); });
$('searchInput').addEventListener('input', loadUsers);
$('createForm').addEventListener('submit', event => { event.preventDefault(); send(API_URL, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:$('createName').value, email:$('createEmail').value})}, async () => { $('createForm').reset(); }); });
$('updateForm').addEventListener('submit', event => { event.preventDefault(); send(`${API_URL}/1`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:$('updateName').value, email:$('updateEmail').value})}, async () => { $('updateForm').reset(); }); });
$('deleteForm').addEventListener('submit', event => { event.preventDefault(); if (confirm('Delete the user with the highest ID?')) send(`${API_URL}/highest`, {method:'DELETE'}, async () => {}); });
loadUsers();
