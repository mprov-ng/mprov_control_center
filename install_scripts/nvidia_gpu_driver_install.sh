#!/bin/bash
. /var/www/mprov_control_center/.env

if [ "$NO_NVIDIA" == "1" ]
then
  exit 0
fi


role="git+https://github.com/NVIDIA/ansible-role-nvidia-driver.git"

extravars="nvidia_driver_skip_reboot=yes"

mkdir -p /tmp/mprov/ansible/roles/
ansible-galaxy role install -p /tmp/mprov/ansible/roles/ $role -f
# run the role, hope you set your variables.....
if [[ $role == git* ]]
then
  role=`basename -s .git $role`
fi

cat <<- EOF > /tmp/role.yaml
- hosts: localhost
  become: true
  gather_facts: true
  tasks:
    - name: Import role $role
      ansible.builtin.include_role:
        name: $role
EOF
ANSIBLE_ROLES_PATH="/tmp/mprov/ansible/roles" ANSIBLE_GATHER=implicit ansible-playbook -i localhost, -c local -e "${extravars}" /tmp/role.yaml
