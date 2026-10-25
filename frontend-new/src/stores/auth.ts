import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export interface AdminUser {
  id: string
  email: string
  full_name: string
  role: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const user = ref<AdminUser | null>(
    JSON.parse(localStorage.getItem('user') ?? 'null'),
  )

  const isAuthenticated = computed(() => !!token.value)

  async function login(email: string, password: string) {
    const response = await axios.post('/api/v1/auth/login', { email, password })

    const data = response.data
    token.value = data.access_token
    localStorage.setItem('access_token', data.access_token)

    // Fetch user profile using the new token
    const meResponse = await axios.get('/api/v1/auth/me', {
      headers: { Authorization: `Bearer ${data.access_token}` },
    })
    user.value = meResponse.data
    localStorage.setItem('user', JSON.stringify(meResponse.data))
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
  }

  return { token, user, isAuthenticated, login, logout }
})
