@Library('pipeline-library') _

pipeline {
  agent { label 'docker' }
  stages {
    stage('Build') {
      steps {
        sh "docker build -t openstax/cnx-easybake:${GIT_COMMIT} ."
      }
    }
    stage('Publish Dev Container') {
      steps {
        // 'docker-registry' is defined in Jenkins under credentials
        withDockerRegistry([credentialsId: 'docker-registry', url: '']) {
          sh "docker push openstax/cnx-easybake:${GIT_COMMIT}"
        }
      }
    }
    stage('Publish Release') {
      when { buildingTag() }
      environment {
        TWINE_CREDS = credentials('pypi-openstax-creds')
        TWINE_USERNAME = "${TWINE_CREDS_USR}"
        TWINE_PASSWORD = "${TWINE_CREDS_PSW}"
      }
      steps {
        withDockerRegistry([credentialsId: 'docker-registry', url: '']) {
          sh "docker tag openstax/cnx-easybake:${GIT_COMMIT} openstax/cnx-easybake:${release}"
          sh "docker tag openstax/cnx-easybake:${GIT_COMMIT} openstax/cnx-easybake:latest"
          sh "docker push openstax/cnx-easybake:${release}"
          sh "docker push openstax/cnx-easybake:latest"
        }
        // Install git, run the python build, upload to pypi, and cleanup
        sh "docker run --rm -e TWINE_USERNAME -e TWINE_PASSWORD -v ${WORKSPACE}:/src:rw --workdir /src python:2-slim /bin/bash -c \"apt-get update && apt-get install -y git && pip install -q twine && python setup.py bdist_wheel --universal && twine upload dist/* && rm -rf dist build *.egg-info versioneer.pyc\""
      }
    }
  }
}
