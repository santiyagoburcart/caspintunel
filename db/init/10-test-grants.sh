#!/bin/bash
# Allow the application DB user to create/drop Django's test database
# (test_<DB_NAME>). Runs once, on first container initialization.
set -e

mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
GRANT ALL PRIVILEGES ON \`test\\_%\`.* TO '${MYSQL_USER}'@'%';
FLUSH PRIVILEGES;
SQL
