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
        release = getVersion()
      }
      steps {
        withDockerRegistry([credentialsId: 'docker-registry', url: '']) {
          sh "docker tag openstax/cnx-easybake:${GIT_COMMIT} openstax/cnx-easybake:${release}"
          sh "docker tag openstax/cnx-easybake:${GIT_COMMIT} openstax/cnx-easybake:latest"
          sh "docker push openstax/cnx-easybake:${release}"
          sh "docker push openstax/cnx-easybake:latest"
        }
      }
    }
  }
}
