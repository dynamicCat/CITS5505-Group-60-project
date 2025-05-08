
$(function () {
  const userSelect      = $('#shareUsers')[0];
  const checkAllMatches = $('#checkAll');
  const shareBtn        = $('#btnShare');

  // —— OptionGroup 辅助构造 —— 
  function OptionGroup(label) {
    this.el = document.createElement('optgroup');
    this.el.label = label;
    this.hasChildren = () => this.el.children.length > 0;
    this.append = o => this.el.appendChild(o);
  }

  // —— 全选/反选比赛 —— 
  checkAllMatches.on('change', () => {
    const checked = checkAllMatches.is(':checked');
    $('.match-checkbox').prop('checked', checked);
    populateUsers();
  });
  $('.match-checkbox').on('change', () => {
    populateUsers();
  });

  // —— 全选/清空 用户列表 —— 
  $('#selectAllUsers').on('click', () => {
    $('#shareUsers option:not(:disabled)').prop('selected', true);
  });
  $('#clearUsers').on('click', () => {
    $('#shareUsers option:selected').prop('selected', false);
  });

  // —— 点击分享按钮 —— 
  shareBtn.on('click', async () => {
    const matchIds = $('.match-checkbox:checked').map((_, el) => el.value).get();
    const usernames = [...userSelect.selectedOptions].map(o => o.value);

    if (!matchIds.length) {
      return alert('⚠️ Please select at least one match.');
    }
    if (!usernames.length) {
      return alert('⚠️ Please select at least one recipient.');
    }

    try {
      const res = await fetch('/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ match_ids: matchIds, usernames })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || res.statusText);

      alert('✅ Share success!');
      location.reload();
    } catch (err) {
      alert('❌ Share failed: ' + err.message);
    }
  });

  // —— 更新用户下拉列表 —— 
  function populateUsers() {
    // 1. 记录之前已经选中的用户名
    const prevSelected = new Set(
      [...userSelect.selectedOptions].map(o => o.value)
    );

    // 2. 找出所有被选中比赛所对应的已分享用户 ID
    const selectedIds = $('.match-checkbox:checked')
      .map((_, el) => parseInt(el.value, 10))
      .get();
    const disabledSet = new Set();
    selectedIds.forEach(id => {
      (sharedMap[id] || []).forEach(uid => disabledSet.add(uid));
    });

    // 3. 清空当前选项
    userSelect.innerHTML = '';

    const selectableGroup = new OptionGroup('Selectable users');
    const disabledGroup   = new OptionGroup('Already shared');

    allUsers.forEach(u => {
      const o = document.createElement('option');
      o.value = u.username;
      o.textContent = u.username;

      // 自己或已分享的放到 disabledGroup
      if (u.username === currentUser || disabledSet.has(u.id)) {
        o.disabled = true;
        o.textContent += (u.username === currentUser) ? ' (Own)' : ' (Shared)';
        disabledGroup.append(o);
      } else {
        // 可选用户：如果之前选中过，保留选中状态
        if (prevSelected.has(u.username)) {
          o.selected = true;
        }
        selectableGroup.append(o);
      }
    });

    if (selectableGroup.hasChildren()) userSelect.appendChild(selectableGroup.el);
    if (disabledGroup.hasChildren())   userSelect.appendChild(disabledGroup.el);
  }

  // —— 页面初次加载时初始化 —— 
  populateUsers();
});
