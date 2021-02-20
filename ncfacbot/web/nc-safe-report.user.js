// ==UserScript==
// @name		Nexus Clash Discord Bot Safe Contents (B4)
// @namespace	https://roadha.us
// @version		0.12
// @description	Sends the components, potions, and spell gems in the safe for consumption by https://github.com/haliphax/ncfacbot
// @author		haliphax
// @match		https://www.nexusclash.com/modules.php?name=Game*
// @grant		GM_getValue
// @grant		GM.getValue
// @grant		GM_setValue
// @grant		GM.setValue
// @grant		GM_xmlhttpRequest
// @grant		GM.xmlHttpRequest
// @require		https://raw.githubusercontent.com/blueimp/JavaScript-MD5/master/js/md5.min.js
// ==/UserScript==

(() => {
	'use strict';

	// GreaseMonkey fix
	if (window.hasOwnProperty('GM')) {
		window.GM_getValue = GM.getValue;
		window.GM_setValue = GM.setValue;
		window.GM_xmlhttpRequest = GM.xmlHttpRequest;
	}

	// constants
	const SETTINGS_ICON = 'https://raw.githubusercontent.com/tailwindlabs/heroicons/master/optimized/outline/chat.svg';

	const safe_forms = document.querySelectorAll(
		'form[name="footlockergrab"]');

	if (safe_forms.length === 0)
		return;

	const
		categories = ['Component', 'Potion', 'Spell'],
		regex_category = /Retrieve ([A-Za-z]+)/,
		regex_spellblind = /^small [a-z]+ gem(, [0-9]+ shots)?( \([0-9]+\))?$/i,
		category_items = {},
		chars = GM_getValue('characters', {}),
		last_known = GM_getValue('last_known', ''),
		last_counts = {},
		profile_link = document.querySelector(
			'#CharacterInfo a[href^="modules.php?name=Game&op=character"]'),
		my_id = /([0-9]+)$/.exec(profile_link.href)[1],
		my_char = chars[my_id],
		cfg_link = document.createElement('a');

	cfg_link.title = 'Discord API settings';
	cfg_link.href = 'javascript:;';
	cfg_link.innerHTML = `
		<img src="${SETTINGS_ICON}"
			style="height: 1em; width: 1em; vertical-align: middle; margin-left: .25em; text-decoration: none;"
			alt="" />
		`;

	cfg_link.addEventListener('click', () => {
		const guild = prompt('Discord guild ID',
			(my_char ? my_char.guild : ''));

		if (!guild || guild.trim().length === 0)
			return;

		const key = prompt('Secret key', (my_char ? my_char.key : ''));

		if (!key || key.trim().length === 0)
			return;

		chars[my_id] = {
			guild: guild.trim(),
			key: key.trim()
		};

		GM_setValue('characters', chars);
	});

	profile_link.parentNode.appendChild(cfg_link);

	if (!chars.hasOwnProperty(my_id)) {
		console.warn('No guild ID for character; aborting');

		return;
	}

	for (let c in categories) {
		const category = categories[c];

		category_items[category] = [];
		last_counts[category] = GM_getValue(`last_count.${category}`, 0);
	}

	for (let f = 0; f < safe_forms.length; f++) {
		const
			form = safe_forms[f],
			match = regex_category.exec(
				form.querySelector('input[type="submit"]').value);

		if (!match)
			continue;

		const category_idx = categories.indexOf(match[1]);

		if (category_idx < 0)
			continue;

		const
			category = categories[category_idx],
			items = form.querySelectorAll('option');

		for (let i = 0; i < items.length; i++) {
			const name = items[i].innerText.trim();

			// if spell blind or can't tell potions apart, skip category
			if ((category == 'Spell' && regex_spellblind.exec(name))
				|| (category == 'Potion' && name.indexOf('Bot') == 0))
			{
				category_items[category].push('0');

				break;
			}

			category_items[category].push(name);
		}
	}

	let same_count = true;

	for (let c in categories) {
		const category = categories[c];

		if (last_counts[category] !== category_items[category].length) {
			same_count = false;

			break;
		}
	}

	if (same_count) {
		const hash = md5(JSON.stringify(category_items));

		if (hash === last_known)
			return;

		GM_setValue('last_known', hash);
	}

	for (let c in categories) {
		const category = categories[c];

		GM_setValue(`last_count.${category}`, category_items[category].length);
	}

	console.log('Posting updated safe contents to server');

	GM_xmlhttpRequest({
		method: 'POST',
		url: 'https://oddnetwork.org/ncfacbot/safe/post',
		data: JSON.stringify({
			guild: my_char.guild,
			key: my_char.key,
			items: category_items,
		}),
		onerror() {
			console.error('Error posting to destination URL');
		},
	});
})();
