#!/bin/bash -eux

export DEBIAN_FRONTEND=noninteractive

sudo zfs set aclmode=passthrough zroot
sudo zfs set aclinherit=passthrough zroot
sudo zfs create -V 2G zroot/samba4sysvol
sudo newfs /dev/zvol/zroot/samba4sysvol
sudo sh -c 'cat >>/etc/fstab' <<EOF
/dev/zvol/zroot/samba4sysvol /var/db/samba4/sysvol ufs       rw,acls 0       0
EOF

sudo mkdir -p /var/db/samba4/sysvol
sudo mount /var/db/samba4/sysvol

apt-get update
apt-get upgrade -y
apt-get dist-upgrade -y

PACKAGES=(
'samba'
'winbind'
'heimdal-clients'
)

# Install needed packages
for package in "${PACKAGES[@]}"; do
    apt-get -y install "$package"
done

# Samba must not be running during the provisioning
rm -fr /etc/systemd/system/samba-ad-dc.service
/usr/bin/systemctl daemon-reload
/usr/bin/systemctl stop samba-ad-dc.service smbd.service nmbd.service winbind.service
/usr/bin/systemctl disable samba-ad-dc.service smbd.service nmbd.service winbind.service

# Domain provision
echo '' > /etc/samba/smb.conf && samba-tool domain provision --realm=LOCAL.DOMAIN --domain=LOCAL --server-role='dc' --dns-backend='SAMBA_INTERNAL' --option 'dns forwarder'='127.0.0.1' --adminpass='4dm1n_s3cr36_v3ry_c0mpl3x' --use-rfc2307 -d 1

# Kerberos settings
rm -fr /etc/krb5.conf
#cp /var/lib/samba/private/krb5.conf /etc/
cat > '/etc/krb5.conf' << EOF
[libdefaults]
    default_realm = LOCAL.DOAMIN
    dns_lookup_realm = false
    dns_lookup_kdc = true
EOF

# Start samba-ad-dc service only
rm -fr /etc/systemd/system/samba-ad-dc.service
/usr/bin/systemctl daemon-reload
/usr/bin/systemctl start samba-ad-dc.service
/usr/bin/systemctl enable samba-ad-dc.service

# Request a kerberos ticket
cat > '/root/.kinit' << EOF
4dm1n_s3cr36_v3ry_c0mpl3x
EOF

/usr/bin/kinit --password-file="/root/.kinit" administrator@LOCAL.DOMAIN

# Add users and groups
/usr/bin/samba-tool user create user1 --use-username-as-cn --surname=Test1 --given-name=User1 --random-password
/usr/bin/samba-tool user create user2 --use-username-as-cn --surname=Test2 --given-name=User2 --random-password
/usr/bin/samba-tool user create user3 --use-username-as-cn --surname=Test3 --given-name=User3 --random-password
/usr/bin/samba-tool user create user4 --use-username-as-cn --surname=Test4 --given-name=User4 --random-password

# Add some groups
/usr/bin/samba-tool group add IT
/usr/bin/samba-tool group add Admins
/usr/bin/samba-tool group add Devs
/usr/bin/samba-tool group add DevOps

# Create members
/usr/bin/samba-tool group addmembers IT Admins,Devs,DevOps,user1
/usr/bin/samba-tool group addmembers Admins user2
/usr/bin/samba-tool group addmembers Devs user3
/usr/bin/samba-tool group addmembers DevOps user4
