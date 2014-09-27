# -*- mode: ruby -*-
# vi: set ft=ruby :

VAGRANTFILE_API_VERSION = "2"
$project_name = "priori"
$port = "9036"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  config.vm.box = "django-base-v2"
  config.vm.box_url = "https://www.dropbox.com/s/vm1ka9f0vun13uu/django-base-v2.box?dl=1"
  config.vm.hostname = $project_name

  config.vm.network "forwarded_port", guest: $port, host: $port

  $script = <<SCRIPT
    echo Provisioning...
    sudo apt-get update
    sudo apt-get -y install vim python-pip
    sudo pip install virtualenvwrapper
    export WORKON_HOME=/home/vagrant/.virtualenvs
    export PIP_DOWNLOAD_CACHE=/home/vagrant/.pip_download_cache
    source /usr/local/bin/virtualenvwrapper.sh
    mkvirtualenv $1
    echo source /usr/local/bin/virtualenvwrapper.sh > /home/vagrant/.bashrc
    echo workon "$1" >> /home/vagrant/.bashrc
    echo alias dj='"python manage.py"' >> /home/vagrant/.bashrc
    echo cd /vagrant/src >> /home/vagrant/.bashrc
    chown -R vagrant: /home/vagrant/
    cd /vagrant
    workon $1
    pip install -r requirements.txt
    cd /vagrant/src
    python manage.py syncdb --noinput
    python manage.py test
    python manage.py runserver 0:$2 &
SCRIPT
  # Non-privileged setup
  config.vm.provision :shell,
    privileged: false,
    inline: $script,
    args: [$project_name, $port]
end
