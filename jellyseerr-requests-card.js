class JellyseerrRequestsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('You need to define an entity');
    }
    this.config = config;
    this.entity = config.entity;
    this.title = config.title || 'Jellyseerr Requests';
    this.showTitle = config.show_title !== false;
    this.showOverview = config.show_overview !== false;
    this.maxOverviewLength = config.max_overview_length || 250;
    
    // Button customization
    this.approveText = config.approve_button_text || 'Accept';
    this.denyText = config.deny_button_text || 'Reject';
    this.showButtonIcons = config.show_button_icons !== false;
    
    // Display options
    this.showPoster = config.show_poster !== false;
    this.showYear = config.show_year !== false;
    this.placeholderImage = config.placeholder_image || '/local/images/poster-placeholder.png';
    
    // Card styling
    this.cardSpacing = config.card_spacing || 8;
    
    // Confirmation
    this.confirmActions = config.confirm_actions !== false;
    this.confirmApproveText = config.confirm_approve_text || 'Approve "{title}"?';
    this.confirmDenyText = config.confirm_deny_text || 'Deny "{title}"?';

    // New option to control action buttons
    this.showActions = config.show_actions !== false;
  }

  set hass(hass) {
    this._hass = hass;
    
    if (!this.content) {
      this.innerHTML = '';
      const card = document.createElement('ha-card');
      if (this.showTitle) {
        card.header = this.title;
      }
      this.content = document.createElement('div');
      const style = document.createElement('style');
      style.textContent = this._getStyles();
      
      this.shadowRoot.appendChild(style);
      this.shadowRoot.appendChild(card);
      card.appendChild(this.content);
    }

    this._updateContent();
  }

  _getStyles() {
    return `
      .container {
        padding: 8px;
        background: var(--base);
        display: flex;
        flex-direction: column;
        gap: ${this.cardSpacing}px;
      }
      
      .request-item {
        position: relative;
        border-radius: 8px;
        padding: 16px;
        background: var(--surface0);
        border: 1px solid var(--divider-color);
        box-shadow: var(--ha-card-box-shadow);
      }
      
      .request-meta {
        position: absolute;
        top: 8px;
        right: 16px;
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 4px;
        color: var(--secondary-text-color);
        font-size: 13px;
        font-weight: 600;
      }
      
      .meta-item {
        display: flex;
        align-items: center;
        gap: 4px;
      }
      
      .request-header {
        margin-bottom: 16px;
        padding-right: 140px;
      }
      
      .request-title {
        font-size: 20px;
        font-weight: bold;
        color: var(--primary-text-color);
        margin-bottom: 4px;
      }
      
      .title-year {
        font-size: 12px;
        font-weight: normal;
        font-style: italic;
        color: var(--secondary-text-color);
        margin-left: 8px;
      }
      
      .request-user {
        font-weight: bold;
        color: var(--primary-text-color);
        font-size: 14px;
      }
      
      .request-date {
        font-size: 12px;
        font-weight: normal;
        font-style: italic;
        color: var(--secondary-text-color);
        margin-left: 8px;
      }
      
      .request-content {
        display: flex;
        gap: 16px;
      }
      
      .poster-container {
        flex-shrink: 0;
        width: 128px;
        height: 192px;
        border-radius: 8px;
        overflow: hidden;
        background: var(--divider-color);
        position: relative;
      }
      
      .poster-image {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }
      
      .no-poster {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--secondary-background-color);
        color: var(--disabled-text-color);
      }
      
      .request-details {
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        gap: 8px;
        min-height: 192px;
      }
      
      .request-overview {
        color: var(--secondary-text-color);
        font-size: 14px;
        line-height: 1.5;
        overflow: hidden;
        display: -webkit-box;
        -webkit-box-orient: vertical;
        -webkit-line-clamp: 6;
      }
      
      .request-actions {
        display: flex;
        gap: 4px;
        margin-top: auto;
      }
      
      .action-button {
        flex: 1;
        padding: 8px 16px;
        border-radius: 8px;
        border: none;
        cursor: pointer;
        font-size: 14px;
        font-weight: bold;
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        color: white;
      }
      
      .approve-button {
        background-color: var(--success-color, #4CAF50);
      }
      
      .approve-button:hover {
        filter: brightness(110%);
        box-shadow: 0 2px 8px rgba(76, 175, 80, 0.3);
      }
      
      .deny-button {
        background-color: var(--error-color, #f44336);
      }
      
      .deny-button:hover {
        filter: brightness(110%);
        box-shadow: 0 2px 8px rgba(244, 67, 54, 0.3);
      }
      
      .no-requests {
        text-align: center;
        padding: 48px;
        color: var(--secondary-text-color);
      }
    `;
  }

  _updateContent() {
    const entityState = this._hass.states[this.entity];
    
    if (!entityState) {
      this.content.innerHTML = '<div class="no-requests">Entity not found</div>';
      return;
    }

    const requests = entityState.attributes.requests || [];
    const requestCount = parseInt(entityState.state) || 0;

    if (requestCount === 0 || requests.length === 0) {
      this.content.innerHTML = `
        <div class="no-requests">
          <ha-icon icon="mdi:check-circle" style="font-size: 48px; color: var(--success-color);"></ha-icon>
          <h3>No requests!</h3>
          <p>This category is empty.</p>
        </div>
      `;
      return;
    }

    let html = '<div class="container">';
    
    requests.forEach((request, index) => {
      const requestDate = request.created_at ? new Date(request.created_at).toLocaleDateString() : '';
      const releaseYear = request.release_date ? new Date(request.release_date).getFullYear() : '';
      
      html += `
        <div class="request-item" data-request-id="${request.id}">
          <div class="request-meta">
            <div class="meta-item">
              <ha-icon icon="mdi:${request.type === 'movie' ? 'movie' : 'television'}" style="width: 24px; height: 24px;"></ha-icon>
              <span>${request.type === 'movie' ? 'Movie' : 'TV Show'}</span>
            </div>
            <div class="meta-item">
              <ha-icon icon="mdi:identifier" style="width: 24px; height: 24px;"></ha-icon>
              <span>${request.id}</span>
            </div>
          </div>
          
          <div class="request-header">
            <div class="request-title">
              ${this._escapeHtml(request.title)}
              ${this.showYear && releaseYear ? `<span class="title-year">${releaseYear}</span>` : ''}
            </div>
            <div class="request-user">
              ${this._escapeHtml(request.requested_by)}
              ${requestDate ? `<span class="request-date">${requestDate}</span>` : ''}
            </div>
          </div>
          
          <div class="request-content">
            ${this.showPoster ? `
              <div class="poster-container">
                ${request.poster_url ? `
                  <img class="poster-image" 
                       src="${request.poster_url}" 
                       alt="${this._escapeHtml(request.title)}"
                       onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                  <div class="no-poster" style="display: none;">
                    <ha-icon icon="mdi:image-off" style="width: 48px; height: 48px;"></ha-icon>
                  </div>
                ` : `
                  <div class="no-poster">
                    <ha-icon icon="mdi:image-off" style="width: 48px; height: 48px;"></ha-icon>
                  </div>
                `}
              </div>
            ` : ''}
            
            <div class="request-details">
              ${this.showOverview && request.overview ? `
                <div class="request-overview">
                  ${this._escapeHtml(request.overview)}
                </div>
              ` : '<div></div>'}
              
              ${this.showActions ? `
              <div class="request-actions">
                <button class="action-button approve-button" data-request-id="${request.id}" data-request-title="${this._escapeHtml(request.title)}">
                  ${this.showButtonIcons ? '<ha-icon icon="mdi:check" style="width: 24px; height: 24px;"></ha-icon>' : ''}
                  ${this.approveText}
                </button>
                <button class="action-button deny-button" data-request-id="${request.id}" data-request-title="${this._escapeHtml(request.title)}">
                  ${this.showButtonIcons ? '<ha-icon icon="mdi:close" style="width: 24px; height: 24px;"></ha-icon>' : ''}
                  ${this.denyText}
                </button>
              </div>
              ` : ''}
            </div>
          </div>
        </div>
      `;
    });
    
    html += '</div>';
    this.content.innerHTML = html;

    // Add event listeners only if actions are shown
    if (this.showActions) {
      this._addEventListeners();
    }
  }

  _addEventListeners() {
    // Approve buttons
    this.shadowRoot.querySelectorAll('.approve-button').forEach(button => {
      button.addEventListener('click', async (e) => {
        const target = e.currentTarget;
        const requestId = parseInt(target.dataset.requestId);
        const requestTitle = target.dataset.requestTitle;
        
        if (!this.confirmActions || confirm(this.confirmApproveText.replace('{title}', requestTitle))) {
          await this._approveRequest(requestId, requestTitle);
        }
      });
    });

    // Deny buttons
    this.shadowRoot.querySelectorAll('.deny-button').forEach(button => {
      button.addEventListener('click', async (e) => {
        const target = e.currentTarget;
        const requestId = parseInt(target.dataset.requestId);
        const requestTitle = target.dataset.requestTitle;
        
        if (!this.confirmActions || confirm(this.confirmDenyText.replace('{title}', requestTitle))) {
          await this._denyRequest(requestId, requestTitle);
        }
      });
    });
  }

  async _approveRequest(requestId, title) {
    try {
      await this._hass.callService('jellyseerr', 'approve_request', {
        request_id: requestId
      });
      
      this._showNotification(`Approved: ${title}`, 'success');
      
      // Update the entity to refresh the display
      setTimeout(() => {
        this._hass.callService('homeassistant', 'update_entity', {
          entity_id: this.entity
        });
      }, 500);
    } catch (error) {
      console.error('Error approving request:', error);
      this._showNotification(`Failed to approve: ${title}`, 'error');
    }
  }

  async _denyRequest(requestId, title) {
    try {
      await this._hass.callService('jellyseerr', 'deny_request', {
        request_id: requestId,
        reason: 'Denied via dashboard'
      });
      
      this._showNotification(`Denied: ${title}`, 'success');
      
      // Update the entity to refresh the display
      setTimeout(() => {
        this._hass.callService('homeassistant', 'update_entity', {
          entity_id: this.entity
        });
      }, 500);
    } catch (error) {
      console.error('Error denying request:', error);
      this._showNotification(`Failed to deny: ${title}`, 'error');
    }
  }

  _showNotification(message, type = 'info') {
    const event = new Event('hass-notification', {
      bubbles: true,
      composed: true,
    });
    event.detail = {
      message: message,
      duration: 3000,
      dismissable: true
    };
    
    this.dispatchEvent(event);
  }

  _escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
      .toString()
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  getCardSize() {
    return 3;
  }

  static getConfigElement() {
    return document.createElement("jellyseerr-requests-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.jellyseerr_pending_requests",
      title: "Pending Requests",
      show_title: true,
      show_overview: true,
      show_poster: true,
      show_year: true,
      max_overview_length: 250,
      show_button_icons: true,
      show_actions: true
    };
  }
}

// Register the card
customElements.define('jellyseerr-requests-card', JellyseerrRequestsCard);

// Add to custom card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'jellyseerr-requests-card',
  name: 'Jellyseerr Requests Card',
  description: 'Display and manage Jellyseerr media requests with poster images',
  preview: false,
  documentationURL: 'https://github.com/yourusername/jellyseerr-requests-card'
});

console.info(
  `%c  JELLYSEERR-REQUESTS-CARD  \n%c  Version 2.0.1  `,
  'color: orange; font-weight: bold; background: black',
  'color: white; font-weight: bold; background: dimgray'
);