# Route map

| Methods | Path | Endpoint |
|---|---|---|
| GET | `/` | web.home |
| POST | `/action/<action>` | web.action |
| GET | `/activity` | web.activity |
| GET | `/add` | web.add |
| GET | `/api/sync` | web.sync |
| POST | `/api/theme` | web.theme |
| GET | `/attachment/<ident>` | web.download |
| GET | `/bill/<ident>` | web.bill |
| GET,POST | `/forgot` | web.forgot |
| GET | `/group/<ident>` | web.group_page |
| GET | `/group/<ident>/expense` | web.expense_page |
| GET | `/groups` | web.groups |
| GET | `/health` | web.health |
| GET | `/invitations` | web.invitations |
| GET,POST | `/login` | web.login_page |
| POST | `/logout` | web.logout |
| GET,POST | `/notifications` | web.notifications |
| GET,POST | `/people` | web.contacts |
| GET,POST | `/profile` | web.profile |
| GET,POST | `/register` | web.register |
| GET | `/relationship/<ident>` | web.relationship_page |
| GET,POST | `/reset/<raw>` | web.reset |
| GET | `/search` | web.search |
| GET | `/split` | web.split_page |
| GET | `/static/<path:filename>` | static |
| GET | `/sw.js` | web.sw |
